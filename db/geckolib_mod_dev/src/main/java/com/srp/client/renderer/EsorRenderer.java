package com.srp.client.renderer;

import com.srp.client.model.EsorModel;
import com.srp.entity.EsorEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class EsorRenderer extends GeoEntityRenderer<EsorEntity> {

    public EsorRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new EsorModel());
    }
}
