package com.srp.client.renderer;

import com.srp.client.model.AlafhaModel;
import com.srp.entity.AlafhaEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class AlafhaRenderer extends GeoEntityRenderer<AlafhaEntity> {

    public AlafhaRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new AlafhaModel());
    }
}
