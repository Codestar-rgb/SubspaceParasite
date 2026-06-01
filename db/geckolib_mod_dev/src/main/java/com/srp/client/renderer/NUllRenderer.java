package com.srp.client.renderer;

import com.srp.client.model.NUllModel;
import com.srp.entity.NUllEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class NUllRenderer extends GeoEntityRenderer<NUllEntity> {

    public NUllRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new NUllModel());
    }
}
